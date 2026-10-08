"""API del tablero de forma de adquisición (Organización)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from server.adquisicion import _job_ve_tablero, tablero_adquisicion
from server.authz import current_user, login_required, permission_required

adq_bp = Blueprint("adquisicion", __name__, url_prefix="/api/adquisicion")


@adq_bp.get("/tablero")
@login_required
@permission_required("view_adquisicion_dashboard")
def get_tablero():
    user = current_user()
    if not _job_ve_tablero(user):
        return jsonify(
            {
                "ok": False,
                "error": "Este tablero está reservado a Coordinador y Director operativo.",
            }
        ), 403
    return jsonify({"ok": True, **tablero_adquisicion(user)})
