"""Router unificado WhatsApp — detecta Twilio (form-data) vs Meta (JSON) por Content-Type."""

import json
import logging
from typing import Callable, Awaitable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from . import meta as wh_meta
from . import twilio_helper as wh_twilio

logger = logging.getLogger(__name__)


def create_whatsapp_router(
    app_id:            str,
    resolver_meta:     Callable[[str], dict | None],
    resolver_twilio:   Callable[[str], dict | None],
    run_agent:         Callable,
    get_historial:     Callable[[str], Awaitable[list]],
    save_historial:    Callable[[str, list], Awaitable[None]],
    meta_verify_token: str = "",
    meta_app_secret:   str = "",
) -> APIRouter:
    """
    Factory que devuelve un APIRouter con GET y POST /whatsapp.
    Cada app pasa sus propios resolvers y callbacks sin que el router
    conozca la lógica de negocio.
    """
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
    async def whatsapp_unified(request: Request):
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            return await _handle_twilio(request)
        return await _handle_meta(request)

    async def _handle_twilio(request: Request) -> PlainTextResponse:
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

        session_id = wh_twilio.session_key(numero_club, numero_jugador)
        historial  = await get_historial(session_id)
        tenant_id  = club["tenant_id"]
        logger.info("whatsapp_incoming | app=%s | tenant=%s | proveedor=twilio", app_id, tenant_id)
        respuesta, historial_nuevo = run_agent(
            historial       = historial,
            mensaje_usuario = Body,
            tenant_id       = tenant_id,
            tenant_params   = club,
            numero_usuario  = numero_jugador,
        )
        await save_historial(session_id, historial_nuevo)
        return wh_twilio.twiml_response(respuesta)

    async def _handle_meta(request: Request) -> PlainTextResponse:
        payload_bytes = await request.body()
        signature     = request.headers.get("X-Hub-Signature-256", "")

        if meta_app_secret and not wh_meta.verificar_firma(payload_bytes, signature, meta_app_secret):
            raise HTTPException(status_code=403, detail="Firma inválida")

        try:
            data = json.loads(payload_bytes)
        except Exception:
            return PlainTextResponse("ok", status_code=200)

        mensaje = wh_meta.parsear_mensaje(data)
        if mensaje is None:
            return PlainTextResponse("ok", status_code=200)

        phone_number_id = mensaje["phone_number_id"]
        numero_usuario  = mensaje["numero_usuario"]
        texto           = mensaje["texto"]

        club = resolver_meta(phone_number_id)
        if club is None:
            return PlainTextResponse("ok", status_code=200)

        if not club.get("meta_access_token"):
            return PlainTextResponse("ok", status_code=200)

        tenant_id  = club["tenant_id"]
        session_id = wh_meta.session_key(phone_number_id, numero_usuario)
        historial  = await get_historial(session_id)
        logger.info("whatsapp_incoming | app=%s | tenant=%s | proveedor=meta", app_id, tenant_id)
        respuesta, historial_nuevo = run_agent(
            historial       = historial,
            mensaje_usuario = texto,
            tenant_id       = tenant_id,
            tenant_params   = club,
            numero_usuario  = numero_usuario,
        )
        await save_historial(session_id, historial_nuevo)

        wh_meta.enviar_mensaje(
            phone_number_id = phone_number_id,
            numero_usuario  = numero_usuario,
            texto           = respuesta,
            access_token    = club["meta_access_token"],
        )
        return PlainTextResponse("ok", status_code=200)

    return router
