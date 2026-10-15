"""A durable, debounced request to rebuild the static portfolio after photo edits."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import update
from starlette.concurrency import run_in_threadpool

from db.models.gallery_publication import GalleryPublication
from db.session import SessionLocal
from services import cloudflare_pages

logger = logging.getLogger(__name__)


def queue_gallery_publication(db):
    # The migration seeds this singleton. Increment in the same transaction as the edit.
    result = db.execute(
        update(GalleryPublication)
        .where(GalleryPublication.id == 1)
        .values(revision=GalleryPublication.revision + 1, changed_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        raise RuntimeError("Gallery publication migration has not been applied")


def publish_pending_gallery(*, now=None, force=False):
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        state = db.get(GalleryPublication, 1)
        if state is None:
            raise RuntimeError("Gallery publication migration has not been applied")
        if not force and state.revision <= state.requested_revision:
            return
        changed_at = state.changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        if not force and (now - changed_at).total_seconds() < 15:
            return
        revision = state.revision
    # Never hold a database transaction open while contacting Cloudflare.
    cloudflare_pages.trigger_deploy()
    with SessionLocal() as db:
        db.execute(update(GalleryPublication).where(
            GalleryPublication.id == 1,
            GalleryPublication.requested_revision < revision,
        ).values(requested_revision=revision))
        db.commit()
    logger.info("Static gallery rebuild requested for revision %s", revision)


def request_gallery_publication():
    """Publish immediately and acknowledge pending edits, including manual rebuilds."""
    publish_pending_gallery(force=True)


async def _publication_worker():
    while True:
        delay = 5
        try:
            await run_in_threadpool(publish_pending_gallery)
        except Exception as error:
            # Exception messages may contain the secret hook URL. Log only the type.
            logger.warning("Gallery rebuild request failed (%s); retrying in 60 seconds", type(error).__name__)
            delay = 60
        await asyncio.sleep(delay)


@asynccontextmanager
async def publication_lifespan(app):
    configured = cloudflare_pages.is_deploy_configured()
    task = asyncio.create_task(_publication_worker()) if configured else None
    if not configured:
        logger.warning("Static gallery rebuilds are disabled: configure CLOUDFLARE_PAGES_DEPLOY_HOOK_URL")
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
