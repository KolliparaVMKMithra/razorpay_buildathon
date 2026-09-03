import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RingWatch — Fraud Ring Detection",
  description: "Real-time coordinated fraud ring detection for Razorpay AI Buildathon",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
