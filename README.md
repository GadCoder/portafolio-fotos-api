# Photography portfolio API

## Featured photographs

Open `/admin-page` and click **Editar** below a photo to open its dedicated edit
screen. Select **Destacar fotografía**, choose the wide or contained layout,
and click **Guardar cambios**. Title, location, year, and series slug
are optional. Unchecking the option restores the regular gallery presentation
without removing the photo or clearing its captions.

The edit screen previews the photograph and loads its saved metadata. **Cancelar**
and **Volver a las fotos** return to the gallery page you came from. The admin
gallery shows photo previews, featured badges, and edit/delete actions.

Admin gallery/editor styles and the edit script use content-based URL versions
so deployments request the current assets even when the CDN caches older files.

`GET /photo/get-all-photos/` returns the existing image fields and optional
`featured`, `featuredLayout`, `title`, `location`, `year`, `seriesSlug`, `width`,
and `height`. Photo IDs and public sorting remain unchanged.

`PATCH /photo/{photo_id}/presentation` accepts those presentation fields as
JSON, requires an authenticated admin session and the `X-CSRF-Token` header,
and returns the updated photo. Omitted fields are retained; nullable caption
fields can be cleared with `null`. Layout accepts `wide`, `contained`, or `null`
(the frontend defaults to wide). Year must be an integer from 1 to 9999.

```json
{
  "featured": true,
  "featuredLayout": "contained",
  "title": "Costa",
  "location": "Lima",
  "year": 2026
}
```

Apply migration `20261014_01` before running the updated application:

```sh
uv sync --locked
uv run alembic upgrade head
```

The standalone admin JSON API is available under `/admin/api`. First call
`GET /admin/api/session` to obtain a short-lived anonymous login CSRF value;
send it in `X-CSRF-Token` with `POST /admin/api/login` and JSON `user` and
`password`. Authenticated requests use the returned session CSRF value for
logout, upload, presentation updates, deletion, and deployment triggering.
Session cookies are host-only, HttpOnly, SameSite=Lax, and Secure by default. Set `APP_ENV` explicitly to `local`, `dev`, `development`, `test`, or `testing`
before `COOKIE_SECURE=false` can disable Secure; elsewhere cookies remain Secure.
Configure `ADMIN_SESSION_MAX_AGE` (seconds,
bounded to 60 seconds–7 days; default 8 hours), and `PORTFOLIO_ORIGINS` as a
comma-separated allowlist for public read access. The cookie is intended to be
proxied by a same-origin frontend/BFF; credentialed wildcard CORS is disabled.

`POST /admin/api/deploy` uses the normal admin session, Origin, and CSRF checks
and returns `202 {"status":"queued"}` after Cloudflare accepts the request. Set
`CLOUDFLARE_PAGES_DEPLOY_HOOK_URL` only on the API service (for example, as a
Dokploy secret); never put the hook URL in the frontend bundle. Create the hook
in the Cloudflare Pages project for the production branch. The endpoint returns
503 until the hook is configured, and upstream failures return a generic 502.
The deploy hook URL is a bearer secret; rotate it in Cloudflare if exposed.

Apply Alembic migration `20261015_01` for persistent revocable sessions. The
database stores only a SHA-256 digest of the opaque session cookie, never the
cookie bearer itself.

The container runs migrations automatically on startup. Existing photos remain
unfeatured and keep their original image metadata. New uploads also store their
dimensions after EXIF orientation correction. The static portfolio reads
photo data during deployment; see the publishing setup below.

## Stable static gallery and automatic publishing

The portfolio now includes image geometry and final responsive layouts in its
static HTML/CSS. It reads this API at build time. A visitor no longer refreshes
photo data while viewing the page. Saved edits appear after the next successful
Cloudflare Pages deployment.

Create a **production branch** deploy hook in the Pages project's **Settings →
Builds → Deploy hooks**, following [Cloudflare's deploy hook guide](https://developers.cloudflare.com/pages/configuration/deploy-hooks/).
Save its secret URL in the API's Dokploy Compose environment:

```dotenv
CLOUDFLARE_PAGES_DEPLOY_HOOK_URL=https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/REPLACE_WITH_SECRET_ID
```

Keep this setting on the API only. Deploy the API with migration `20261015_02`
before deploying the frontend. The container applies migrations on startup.
Uploads, edits and deletions update a durable publication revision in the same
transaction as the photo change. The worker waits for 15 seconds without edits,
then requests a build. Pending revisions survive restarts; failed hook requests
retry every 60 seconds. Edits arriving during a hook request remain pending for
a subsequent build. The admin’s **Deploy public gallery** button uses the same
adapter and acknowledges pending edits when its immediate request succeeds,
preventing a redundant automatic build for those edits. A successful hook request
means a build was queued, not
that Pages has completed deployment; check Pages for build failures. Without
the setting, edits remain pending until a configured API process starts.

Backfill legacy photos once, inside the API container with its existing database
and R2 credentials. Preview first, then save:

```sh
uv run python -m scripts.backfill_photo_dimensions
uv run python -m scripts.backfill_photo_dimensions --apply
```

The command tries both the URL-relative R2 key and the full URL path, preserving
legacy folder prefixes. If all candidates return `NoSuchKey`, it reads the exact
public original URL from the configured HTTPS image host instead. Authentication
and other storage errors remain failures. Downloads are limited to 50 MB with a
30-second timeout for public requests. The command accounts for EXIF orientation, skips
records with valid dimensions, and saves successful results in one transaction.
It exits nonzero if any image failed; rerun to retry those images. Applying a
backfill also queues a build. New uploads already save normalized dimensions.
The frontend also resolves legacy dimensions during builds, so it can render
stable images while this database backfill is pending.
