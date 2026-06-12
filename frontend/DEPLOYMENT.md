# Frontend-Only Deployment

This dashboard can be deployed on its own without deploying the backend.

## Recommended options

### Vercel

1. Create a new Vercel project from this GitHub repository.
2. Set the **Root Directory** to `frontend`.
3. Keep the build command as `npm run build`.
4. Use the default output for Next.js (`.next`).
5. Add these environment variables:
   - `NEXT_PUBLIC_API_URL` = backend API URL
   - `NEXT_PUBLIC_WS_URL` = backend WebSocket URL

With this setup, changes in backend folders will not affect the frontend deployment unless the `frontend` folder itself changes.

### Docker

Build and run the frontend image from the `frontend` directory:

```bash
docker build -t agentx-frontend .
docker run -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=https://your-backend-url \
  -e NEXT_PUBLIC_WS_URL=wss://your-backend-url \
  agentx-frontend
```

## Verify the frontend before deployment

From the `frontend` folder:

```bash
npm install
npm run build
```

If this passes, the frontend is ready for isolated deployment.