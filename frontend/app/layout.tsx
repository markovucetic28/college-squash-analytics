import type { Metadata } from "next";
import Header from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: "College Squash Analytics",
  description: "Varsity college squash schedules, team histories, player ratings, and matchup estimates.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Header /><main>{children}</main><footer>Independent college squash analytics · Project estimates are not official CSA forecasts.</footer></body></html>;
}
