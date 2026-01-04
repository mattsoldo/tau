# Tau Lighting Control - Frontend

Modern web interface for the Tau smart lighting control system, built with Next.js 14+, TypeScript, and Tailwind CSS.

## Features

- 📱 Responsive design for mobile, tablet, and desktop
- 🎨 Real-time lighting control interface
- 🌅 Circadian schedule visualization and editing
- 🎭 Scene management and activation
- 📊 Live status updates via WebSocket
- ⚡ Optimized performance with React Query

## Architecture

```
frontend/
├── src/
│   ├── app/              # Next.js App Router pages
│   │   ├── layout.tsx    # Root layout
│   │   ├── page.tsx      # Home page
│   │   └── globals.css   # Global styles
│   ├── components/       # React components
│   │   ├── ui/           # Reusable UI components
│   │   ├── fixtures/     # Fixture control components
│   │   ├── groups/       # Group control components
│   │   └── scenes/       # Scene management components
│   ├── lib/              # Utility functions
│   │   ├── api.ts        # API client
│   │   ├── websocket.ts  # WebSocket connection
│   │   └── utils.ts      # Helper functions
│   ├── hooks/            # Custom React hooks
│   │   ├── useFixtures.ts
│   │   ├── useGroups.ts
│   │   └── useWebSocket.ts
│   ├── stores/           # Zustand state stores
│   │   ├── useFixtureStore.ts
│   │   └── useUIStore.ts
│   └── types/            # TypeScript type definitions
│       └── tau.ts        # Tau system types
├── public/               # Static assets
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── next.config.js
```

## Development Setup

### Local Development

1. Install dependencies:
```bash
npm install
```

2. (Optional) Set up environment variables for development:
```bash
# Create .env.local file (optional - defaults to localhost:8000)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

**Note**: The frontend automatically detects the API URL from the browser's hostname in production, so these variables are only needed if you want to override the default behavior in development.

3. Run the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

### Docker Development

```bash
# From project root
docker-compose up frontend
```

## Building for Production

```bash
npm run build
npm start
```

## Technology Stack

- **Framework**: Next.js 14+ with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Data Fetching**: TanStack React Query
- **Real-time**: Socket.io Client
- **Charts**: Recharts
- **Icons**: Lucide React

## Code Quality

- **Linting**: ESLint with Next.js config
- **Type Checking**: TypeScript strict mode
- **Formatting**: Prettier

Run checks:
```bash
npm run lint
npm run type-check
npm run format
```

## Key Pages

### Home (/)
- Dashboard overview
- Quick access to rooms and scenes
- System status

### Rooms (/rooms)
- Room-by-room lighting control
- Group management
- Real-time status updates

### Scenes (/scenes)
- Scene library
- Scene activation
- Scene creation and editing

### Schedule (/schedule)
- Circadian profile visualization
- Schedule editing
- Profile assignment to groups

### Settings (/settings)
- Fixture configuration
- Switch configuration
- System settings

## API Integration

The frontend communicates with the Python daemon via:

1. **REST API**: CRUD operations for configuration
2. **WebSocket**: Real-time state updates and control

Example API usage:
```typescript
import { api } from '@/lib/api';

// Get all fixtures
const fixtures = await api.get('/api/fixtures');

// Control a fixture
await api.post('/api/control/fixture/1', {
  brightness: 800,
  cct: 3000,
  transition_ms: 1000
});
```

## WebSocket Events

Subscribe to real-time updates:
```typescript
import { useWebSocket } from '@/hooks/useWebSocket';

const { subscribe } = useWebSocket();

subscribe('fixture_state_changed', (data) => {
  console.log('Fixture updated:', data);
});
```

## Deployment

The frontend can be deployed:

1. **Standalone**: As a standalone Next.js application
2. **Docker**: Using the provided Dockerfile
3. **Static Export**: For serving from Nginx (requires API proxy configuration)

### Docker Deployment
```bash
docker build -t tau-frontend .
docker run -p 3000:3000 tau-frontend
```

### Environment Variables

- `NEXT_PUBLIC_API_URL`: Backend API base URL (optional - auto-detected from browser hostname)
- `NEXT_PUBLIC_WS_URL`: WebSocket connection URL (optional - auto-detected from browser hostname)
- `NODE_ENV`: Environment mode (development/production)

**Dynamic API Detection**: In production, the frontend automatically detects the API URL from the browser's current hostname, eliminating the need to hardcode IP addresses during deployment. This allows the same build to work on any network without reconfiguration.
