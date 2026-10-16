# Photography portfolio API

## Featured photographs

Open `/admin-page` and click **Editar** below a photo to open its dedicated edit
screen. Select **Destacar fotografía**, choose the wide or contained layout,
and click **Guardar cambios**. Title, location, and series membership are
optional. A supplied `seriesSlug` must reference an existing series.
Unchecking the option restores the regular gallery presentation
without removing the photo or clearing its captions.

The edit screen previews the photograph and loads its saved metadata. **Cancelar**
and **Volver a las fotos** return to the gallery page you came from. The admin
gallery shows photo previews, featured badges, and edit/delete actions.

Admin gallery/editor styles and the edit script use content-based URL versions
so deployments request the current assets even when the CDN caches older files.

`GET /photo/get-all-photos/` returns the existing image fields and optional
`featured`, `featuredLayout`, `title`, `location`, `seriesSlug`,
`seriesId`, `seriesPosition`, `showInPreview`, `previewPosition`, `width`, and
`height`. Photo IDs and the existing photo endpoint sorting remain unchanged.

`PATCH /photo/{photo_id}/presentation` accepts those presentation fields as
JSON, requires an authenticated admin session and the `X-CSRF-Token` header,
and returns the updated photo. Omitted fields are retained; nullable caption
fields can be cleared with `null`. Layout accepts `wide`, `contained`, or `null`
(the frontend defaults to wide).

```json
{
  "featured": true,
  "featuredLayout": "contained",
  "title": "Costa",
  "location": "Lima"
}
```

Apply migrations through the current head before running the updated application:

```sh
uv sync --locked
uv run alembic upgrade head
```

## Series API

Migration `20261015_03` creates structured series and photo membership fields.
It does not create series from the legacy `series_slug` field or assign any
photos; all photos remain unassigned for the owner to curate in the admin.
Migration `20261015_04` adds the optional year to each series and removes the
old `photos.year` column. It does not copy photo-year values to series.

Public `GET /series/` returns published series ordered by `position`, each with
`id`, `slug`, `title`, `description`, `year`, `position`, `totalPhotos`,
`previewPhotos`, and all ordered `photos`. `GET /series/{slug}/` returns the
same object for one published series. Unpublished series return 404 on the
detail route. Each photo includes `seriesId`, `seriesPosition`,
`showInPreview`, and `previewPosition` alongside the existing photo fields.
Series with up to five photos use all photos for `previewPhotos`; larger
published series require one to five selected preview photos.

Authenticated, Origin- and CSRF-protected admin endpoints are:

- `GET /admin/api/series` lists drafts and published series with photos.
- `POST /admin/api/series` creates metadata (`slug`, `title`, optional
  `description`, `year`, `position`, and `published`). Omitted position appends it.
- `PATCH /admin/api/series/{id}` updates those metadata fields.
- `DELETE /admin/api/series/{id}` detaches member photos; it never deletes
  photo records or image assets.
- `PUT /admin/api/series/order` accepts `{"seriesIds":[...]}` and must include
  every series ID exactly once.
- `PUT /admin/api/series/{id}/photos` accepts `{"photoIds":[...]}` to replace
  full membership and order. Photos already assigned to another series are
  rejected.
- `PUT /admin/api/series/{id}/preview` accepts `{"photoIds":[...]}` to replace
  preview selection and order, with at most five unique IDs belonging to that
  series.

Publishing and every later edit must preserve the preview rule for series with
more than five photos. The same check applies to photo membership edits,
legacy `seriesSlug` presentation updates, and photo deletion. Public-facing
series and photo mutations queue a durable gallery publication revision in the
same database transaction. Run `uv run pytest` for the backend suite.

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

Keep this setting on the API only. Deploy the API with migration `20261015_03`
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
