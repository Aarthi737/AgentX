'use client';
<<<<<<< HEAD
=======
'use client';
>>>>>>> a2b603800cba3f35760fac54997e9638ad2f48e0
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () => new QueryClient({
      defaultOptions: { queries: { staleTime: 10_000, retry: 2 } },
    })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
