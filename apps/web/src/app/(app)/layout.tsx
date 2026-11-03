import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "Espace de travail",
};

export default function LayoutApplication({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
