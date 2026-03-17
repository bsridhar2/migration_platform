# Migration Platform UI

Next.js 14 frontend for the AI Migration Platform.

## Tech Stack

| Layer | Package | Purpose |
|-------|---------|---------|
| Framework | Next.js 14 (App Router) | SSR, routing, API rewrites |
| Language | TypeScript 5.x | Type safety |
| Styling | Tailwind CSS 3.x | Utility classes |
| Data fetching | SWR | Polling + mutation |
| HTTP client | Axios | FastAPI communication |
| Diagrams | Mermaid.js 11 | Architecture + sequence diagrams |
| Code viewer | Monaco Editor | View generated code |
| Animations | Framer Motion | Page transitions |
| Real-time | WebSocket (native) | Live progress streaming |
| Notifications | react-hot-toast | Toast messages |

## Why Next.js (not plain React/Vite)?

The migration tool has 6 nested route screens under `/migration/[id]/...`, which benefits from:

- **App Router layouts** — persistent sidebar navigation re-uses without remounting
- **API rewrites** — `/api/*` proxied to FastAPI without CORS configuration
- **`next/dynamic`** — Monaco Editor loaded client-side only (heavy bundle)
- **`next/font`** — Inter font optimisation built-in

## Screen Flow

```
/                                   ← Home — Git URL input
/migration/[id]/scanning            ← Phase A live progress (WebSocket)
/migration/[id]/analysis            ← Architecture diagrams, SOAP map
/migration/[id]/review   ★          ← APPROVAL GATE — approve / reject
/migration/[id]/generating          ← Phase B code gen + Monaco preview
/migration/[id]/complete            ← Download React ZIP + Spring Boot ZIP
```

## Quick Start

```bash
cd migration-ui
cp .env.local.example .env.local
# Edit .env.local — set NEXT_PUBLIC_API_URL=http://localhost:8000

npm install
npm run dev
# → http://localhost:3000
```

## Project Structure

```
src/
├── app/                          ← Next.js App Router pages
│   ├── layout.tsx                ← Root layout (dark theme, Toaster)
│   ├── page.tsx                  ← Home — repo URL form
│   └── migration/[id]/
│       ├── layout.tsx            ← Sidebar navigation (shared)
│       ├── scanning/page.tsx     ← Live progress tracker
│       ├── analysis/page.tsx     ← Diagrams + SOAP panel
│       ├── review/page.tsx       ← ★ Approval gate
│       ├── generating/page.tsx   ← Code gen + Monaco viewer
│       └── complete/page.tsx     ← Download center
├── components/
│   ├── ui/                       ← ProgressBar, StatusBadge, Spinner
│   └── migration/                ← DiagramViewer, SoapIntegrationPanel, ApprovalPanel
├── hooks/
│   ├── useWebSocket.ts           ← Reconnecting WS with exponential backoff
│   └── useMigration.ts           ← SWR polling + approval mutation
├── lib/
│   ├── api.ts                    ← Axios typed API client
│   └── utils.ts                  ← cn(), statusLabel(), statusColor()
└── types/
    └── index.ts                  ← All shared TypeScript interfaces
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI backend URL |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | WebSocket base URL |

## Build

```bash
npm run build   # Production build
npm run start   # Start production server
npm run lint    # ESLint
npm run type-check  # TypeScript check (no emit)
```
