# Photography portfolio API

## Featured photographs

Open `/admin-page`, select **Destacar fotografía** on an existing photo, choose
the wide or contained layout, and save. Title, location, year, and series slug
are optional. Unchecking the option restores the regular gallery presentation
without removing the photo or clearing its captions.

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

The container runs migrations automatically on startup. Existing photos remain
unfeatured and keep their original image metadata. New uploads also store their
dimensions after EXIF orientation correction. The static portfolio refreshes
photo data on each visit, so saved presentation changes appear after reloading.
