import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import { AuthGate } from "@/components/auth";
export const metadata: Metadata = {
  title: {
    default: "AutoRCA-X · Engineering intelligence",
    template: "%s · AutoRCA-X",
  },
  description:
    "An explainable multi-agent workspace for root cause analysis, evidence-backed fixes, and human review.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <Providers>
          <AuthGate>
            <Shell>{children}</Shell>
          </AuthGate>
        </Providers>
      </body>
    </html>
  );
}
