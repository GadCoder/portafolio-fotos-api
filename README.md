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
logout, upload, presentation updates, and deletion. Session cookies are
host-only, HttpOnly, SameSite=Lax, and Secure by default. Configure
`COOKIE_SECURE=false` only for local HTTP tests, `ADMIN_SESSION_MAX_AGE` (seconds,
bounded to 60 seconds–7 days; default 8 hours), and `PORTFOLIO_ORIGINS` as a
comma-separated allowlist for public read access. The cookie is intended to be
proxied by a same-origin frontend/BFF; credentialed wildcard CORS is disabled.

Apply Alembic migration `20261015_01` for persistent revocable sessions. The
database stores only a SHA-256 digest of the opaque session cookie, never the
cookie bearer itself.

The container runs migrations automatically on startup. Existing photos remain
unfeatured and keep their original image metadata. New uploads also store their
dimensions after EXIF orientation correction. The static portfolio refreshes
photo data on each visit, so saved presentation changes appear after reloading.
