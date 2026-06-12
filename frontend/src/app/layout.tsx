// AgentX — Root Layout
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';
import { Sidebar } from '@/components/layout/Sidebar';
import { Toaster } from 'react-hot-toast';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'AgentX — Autonomous Code Review',
  description: 'LangGraph 9-Agent Pipeline | Agentic AI Hackathon 2026 | ASTRA Lab, IIT Madras',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-gray-950 text-gray-100 min-h-screen`}>
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-auto p-6">
              {children}
            </main>
          </div>
          <Toaster
            position="top-right"
            toastOptions={{
              style: { background: '#1f2937', color: '#f9fafb', border: '1px solid #374151' },
            }}
          />
        </Providers>
      </body>
    </html>
  );
}
