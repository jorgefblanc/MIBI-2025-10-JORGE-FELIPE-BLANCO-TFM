"""Alta pública: solicitudes de JOB pendiente."""

JOB_PENDING_TIPO = "JOB_PENDIENTE"


def insert_job_pending_notification(conn, *, user_id, email, nombre, roll):
    roll_txt = "Operador" if (roll or "").upper() == "OPERATIVO" else "Asistencial"
    conn.execute(
        """
        INSERT INTO notificaciones_admin (
            tipo, mensaje, solicitante_id, solicitante_email,
            solicitante_nombre, estado, creation_date
        ) VALUES (?, ?, ?, ?, ?, 'PENDIENTE', datetime('now'))
        """,
        (
            JOB_PENDING_TIPO,
            (
                f"Asignación de JOB pendiente. {nombre} ({email}) se registró "
                f"como {roll_txt} sin cargo. El administrador o el director "
                f"{'operativo' if roll_txt == 'Operador' else 'asistencial'} "
                f"debe asignar el JOB."
            ),
            int(user_id),
            email,
            nombre,
        ),
    )


def resolve_job_pending_notifications(conn, usuario_id):
    if not usuario_id:
        return 0
    cur = conn.execute(
        """
        UPDATE notificaciones_admin
        SET estado = 'RESUELTA'
        WHERE solicitante_id = ?
          AND tipo = ?
          AND estado = 'PENDIENTE'
        """,
        (int(usuario_id), JOB_PENDING_TIPO),
    )
    return cur.rowcount
