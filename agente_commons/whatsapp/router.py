"""Router unificado WhatsApp — detecta Twilio (form-data) vs Meta (JSON) por Content-Type."""

import asyncio
import inspect
import json
import logging
from typing import Callable, Awaitable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from . import meta as wh_meta
from . import twilio_helper as wh_twilio

logger = logging.getLogger(__name__)


async def _llamar_run_agent(run_agent_fn, **kwargs):
    """Despacha run_agent sin importar si es sync o async."""
    if inspect.iscoroutinefunction(run_agent_fn):
        return await run_agent_fn(**kwargs)
    else:
        return await asyncio.to_thread(run_agent_fn, **kwargs)


def create_whatsapp_router(
    app_id:               str,
    resolver_meta:        Callable[[str], dict | None],
    resolver_twilio:      Callable[[str], dict | None],
    run_agent:            Callable,
    get_historial:        Callable[[str], Awaitable[list]],
    save_historial:       Callable[[str, list], Awaitable[None]],
    meta_verify_token:    str = "",
    meta_app_secret:      str = "",
    twilio_account_sid:   str = "",
    twilio_auth_token:    str = "",
    twilio_whatsapp_from: str = "",
) -> APIRouter:
    """
    Factory que devuelve un APIRouter con GET y POST /whatsapp.
    Cada app pasa sus propios resolvers y callbacks sin que el router
    conozca la lógica de negocio.

    run_agent puede ser síncrono o async. El handler devuelve 200 a Meta /
    TwiML vacío a Twilio de forma inmediata; run_agent se ejecuta en
    background via BackgroundTasks para evitar reintentos por timeout.
    """
    if not meta_app_secret:
        logger.warning(
            "create_whatsapp_router | app=%s | meta_app_secret no configurado — "
            "verificación de firma Meta deshabilitada",
            app_id,
        )

    router = APIRouter()

    @router.get("/whatsapp")
    async def whatsapp_verify(
        hub_mode:         str = Query(None, alias="hub.mode"),
        hub_verify_token: str = Query(None, alias="hub.verify_token"),
        hub_challenge:    str = Query(None, alias="hub.challenge"),
    ):
        if (
            meta_verify_token
            and hub_mode == "subscribe"
            and hub_verify_token == meta_verify_token
        ):
            return PlainTextResponse(hub_challenge or "", status_code=200)
        raise HTTPException(status_code=403, detail="Verificación fallida")

    @router.post("/whatsapp")
    async def whatsapp_unified(request: Request, background_tasks: BackgroundTasks):
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            return await _handle_twilio(request, background_tasks)
        return await _handle_meta(request, background_tasks)

    async def _handle_twilio(request: Request, background_tasks: BackgroundTasks) -> PlainTextResponse:
        form           = await request.form()
        From           = form.get("From", "")
        To             = form.get("To", "")
        Body           = form.get("Body", "")
        numero_club    = wh_twilio.normalizar_numero(To)
        numero_jugador = wh_twilio.normalizar_numero(From)

        club = resolver_twilio(numero_club)
        if club is None:
            return wh_twilio.twiml_response(
                "Este número no está disponible. Comuníquese directamente con el club."
            )

        tenant_id = club.get("tenant_id")
        if tenant_id is None:
            logger.error(
                "resolver_twilio_missing_tenant_id | app=%s | numero_club=%s",
                app_id, numero_club,
            )
            return wh_twilio.twiml_response("Error interno. Por favor intente más tarde.")

        background_tasks.add_task(
            _procesar_twilio,
            numero_club    = numero_club,
            numero_jugador = numero_jugador,
            body           = Body,
            club           = club,
        )
        return wh_twilio.twiml_response("")

    async def _procesar_twilio(numero_club: str, numero_jugador: str, body: str, club: dict):
        session_id = wh_twilio.session_key(numero_club, numero_jugador)
        historial  = await get_historial(session_id)
        tenant_id  = club["tenant_id"]
        logger.info("whatsapp_processing | app=%s | tenant=%s | proveedor=twilio", app_id, tenant_id)

        try:
            _respuesta, historial_nuevo = await _llamar_run_agent(
                run_agent,
                historial       = historial,
                mensaje_usuario = body,
                tenant_id       = tenant_id,
                tenant_params   = club,
                numero_usuario  = numero_jugador,
            )
        except Exception:
            logger.exception("run_agent_error | app=%s | tenant=%s | proveedor=twilio", app_id, tenant_id)
            return

        await save_historial(session_id, historial_nuevo)

        if twilio_account_sid and twilio_auth_token and twilio_whatsapp_from:
            ok = await asyncio.to_thread(
                wh_twilio.enviar_mensaje,
                numero_jugador,
                _respuesta,
                twilio_account_sid,
                twilio_auth_token,
                twilio_whatsapp_from,
            )
            if not ok:
                logger.error(
                    "enviar_mensaje_twilio_failed | app=%s | tenant=%s | numero=%s",
                    app_id, tenant_id, numero_jugador,
                )

    async def _handle_meta(request: Request, background_tasks: BackgroundTasks) -> PlainTextResponse:
        payload_bytes = await request.body()
        signature     = request.headers.get("X-Hub-Signature-256", "")

        # Rechaza solo si el secret está configurado Y la firma está presente pero es inválida.
        # Requests sin header de firma (pings de consola Meta) son aceptados.
        if meta_app_secret and signature and not wh_meta.verificar_firma(payload_bytes, signature, meta_app_secret):
            raise HTTPException(status_code=403, detail="Firma inválida")

        try:
            data = json.loads(payload_bytes)
        except Exception:
            return PlainTextResponse("ok", status_code=200)

        mensaje = wh_meta.parsear_mensaje(data)
        if mensaje is None:
            return PlainTextResponse("ok", status_code=200)

        club = resolver_meta(mensaje["phone_number_id"])
        if club is None:
            return PlainTextResponse("ok", status_code=200)

        if not club.get("meta_access_token"):
            return PlainTextResponse("ok", status_code=200)

        if club.get("tenant_id") is None:
            logger.error(
                "resolver_meta_missing_tenant_id | app=%s | phone_number_id=%s",
                app_id, mensaje["phone_number_id"],
            )
            return PlainTextResponse("ok", status_code=200)

        background_tasks.add_task(
            _procesar_meta,
            mensaje = mensaje,
            club    = club,
        )
        return PlainTextResponse("ok", status_code=200)

    async def _procesar_meta(mensaje: dict, club: dict):
        session_id = wh_meta.session_key(mensaje["phone_number_id"], mensaje["numero_usuario"])
        historial  = await get_historial(session_id)
        tenant_id  = club["tenant_id"]
        logger.info("whatsapp_processing | app=%s | tenant=%s | proveedor=meta", app_id, tenant_id)

        try:
            respuesta, historial_nuevo = await _llamar_run_agent(
                run_agent,
                historial       = historial,
                mensaje_usuario = mensaje["texto"],
                tenant_id       = tenant_id,
                tenant_params   = club,
                numero_usuario  = mensaje["numero_usuario"],
            )
        except Exception:
            logger.exception("run_agent_error | app=%s | tenant=%s | proveedor=meta", app_id, tenant_id)
            return

        await save_historial(session_id, historial_nuevo)
        ok = wh_meta.enviar_mensaje(
            phone_number_id = mensaje["phone_number_id"],
            numero_usuario  = mensaje["numero_usuario"],
            texto           = respuesta,
            access_token    = club["meta_access_token"],
        )
        if not ok:
            logger.error(
                "enviar_mensaje_failed | app=%s | tenant=%s | numero=%s",
                app_id, tenant_id, mensaje["numero_usuario"],
            )

    return router
