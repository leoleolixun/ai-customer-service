from pathlib import Path


def test_backup_quiesces_and_resumes_periodic_scheduler() -> None:
    script = Path("scripts/backup.sh").read_text(encoding="utf-8")

    assert "beat_was_running=false" in script
    assert 'grep -qx beat <<<"${running_services}" && beat_was_running=true' in script
    assert '[[ "${beat_was_running}" == true ]] && services_to_stop+=(beat)' in script
    assert '[[ "${beat_was_running}" == true ]] && services+=(beat)' in script


def test_restore_keeps_periodic_scheduler_inside_the_maintenance_window() -> None:
    script = Path("scripts/restore.sh").read_text(encoding="utf-8")

    assert "stop -t 60 api worker beat" in script
    assert "up -d --no-deps api worker beat" in script
    assert 'read_key "${ENV_FILE}" APP_REDIS_URL' not in script
    assert "Compose-rendered APP_REDIS_URL" in script
    assert "run --rm --no-deps --entrypoint /bin/sh api" in script
