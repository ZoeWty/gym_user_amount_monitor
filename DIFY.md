# Dify chatbot

The bot asks what you want to do, then answers with the emptiest venue.

**The ranking is not the model's job.** `/api/recommend` sorts the venues and
decides which to exclude; the LLM picks the activity out of the sentence, calls
the tool, and reads the result back. Given the raw numbers, a model will happily
recommend 信義 at "0 people" — which is a venue that is probably shut, not empty.
The endpoint already drops those. Keep that boundary.

## 1. Import the tool

Dify imports OpenAPI specs directly, and FastAPI already publishes one. There is
nothing to write.

**Tools → Custom → Create Custom Tool**, then paste the URL:

```
http://host.docker.internal:8000/openapi.json
```

`host.docker.internal` is deliberate. Inside a Dify container, `localhost` is
that container, not your Mac — the spec declares this base URL for the same
reason. Verified working from `docker-api-1`.

Set **Authorization** to None. The API is read-only and bound to `127.0.0.1`.

You should see five operations. Only `recommendVenue` matters; the others are
there if you want them.

## 2. What the tool returns

```
GET /api/recommend?area=gym&near=xysc&max_km=6&limit=3
```

| Parameter | Meaning |
|---|---|
| `area` | `gym`, `swim`, or `ice` |
| `near` | A **venue id** to measure distance from, not coordinates |
| `max_km` | Only consider venues within this far of `near` |
| `limit` | How many to return (1–12) |

```json
{
  "area": "gym",
  "as_of": "2026-09-24T09:28:06Z",
  "stale_minutes": 3,
  "near": { "id": "xysc", "name": "信義" },
  "results": [
    { "id": "wssc", "name": "文山", "current": 31, "capacity": 110,
      "usage_pct": 28, "distance_km": 3.9 }
  ]
}
```

`near` takes a venue id rather than a latitude and longitude on purpose. Asking
"which district are you near?" answers the question well enough, and it means no
GPS coordinate is ever sent to the server or into a model's context. The web
dashboard computes distance in the browser for the same reason.

Venue ids: `btsc` 北投, `dasc` 大安, `dtsc` 大同, `jjsc` 中正, `ngsc` 南港,
`nhsc` 內湖, `slsc` 士林, `sssc` 松山, `whsc` 萬華, `wssc` 文山, `xysc` 信義,
`zssc` 中山.

## 3. Build the agent

Create a **Chatflow** (or an Agent), add the `recommendVenue` tool, and give it
this instruction:

```
You help people pick a Taipei sports centre.

First establish what they want to do. If they have not said, ask: gym,
swimming, or the ice rink? Do not guess.

Then ask roughly where they are, offering district names. If they say a
district, map it to that venue's id and pass it as `near`. If they will not
say, omit `near`.

Call recommendVenue. Report its results in the order given.

Rules:
- Never reorder, filter, or add venues. The ranking is already correct.
- Never recommend a venue that is not in the results.
- If stale_minutes is above 30, say the data is that old before answering.
- If results is empty, say so and suggest widening max_km.
- Reply in the language the user wrote in.
```

The rules exist because each one is a failure that has already happened or is
one prompt away: models reorder lists they are told to preserve, invent a
thirteenth venue, and present nine-hour-old numbers as current.

## 4. Put the bubble on the dashboard

Publish the app, then **Publish → Embed in website** and copy the `token` out of
the snippet Dify shows. Put it in `.env` at the repo root:

```
VITE_DIFY_TOKEN=<the token from the snippet>
VITE_DIFY_URL=http://localhost
```

```bash
docker compose up -d --build api
```

The rebuild is required: Vite bakes both values into the bundle, so they are
Docker build args rather than runtime environment. With no token the component
renders nothing, so the dashboard is never left with a button that fails when
pressed.

## 5. Check it works

Ask it three things:

1. **"我現在想運動"** — it should ask gym or swim rather than assuming.
2. **"我在信義附近，想游泳"** — it should call the tool with `area=swim`,
   `near=xysc` and read back the list unchanged.
3. **"哪間最空？"** after the collector has been down a while — it should say
   how old the data is.

Compare its answer against the endpoint directly:

```bash
curl -s "http://localhost:8000/api/recommend?area=swim&near=xysc&limit=3"
```

In the cloud, `VITE_DIFY_URL` has to be an address the *browser* can reach, not
`host.docker.internal` -- that name only resolves inside a container. The two
URLs point at different things and are set independently.

If the bot's order differs from the JSON, the prompt is losing to the model.
Tighten the instruction; do not move ranking into the model.

## In the cloud

Set `PUBLIC_BASE_URL` to the tunnel hostname so the spec advertises a reachable
address, then re-import the tool in Dify:

```yaml
api:
  environment:
    PUBLIC_BASE_URL: https://your-tunnel-hostname
```

If Dify is on a different host from the API, the API has to be reachable from
it — through the tunnel with an Access service token, not by opening port 8000.

## Not done here

- **No Dify app DSL in this repo.** Dify's export format is tied to its version,
  and a YAML that silently fails to import is worse than four minutes of
  clicking. The tool import above is the stable part.
- **No conversation memory.** Each question stands alone. Add it when a
  follow-up like "what about tomorrow morning?" needs to work — which also needs
  the forecast that does not exist yet.
