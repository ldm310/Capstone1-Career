import type { Metadata } from "next";
import localFont from "next/font/local";
import { Geist, Geist_Mono } from "next/font/google";
import { CareerProvider } from "@/components/shared/career-provider";
import "./globals.css";
import "./korean.css";
import "./career.css";
import "./typography.css";
import "./learning-path.css";
import "./controls.css";
const careerFont = localFont({
  src: "./fonts/PretendardVariable.woff2",
  variable: "--font-career-ui",
  weight: "100 900",
  display: "swap",
  fallback: ["Apple SD Gothic Neo", "Malgun Gothic", "sans-serif"],
});
const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});
export const metadata: Metadata = {
  title: {
    default: "Career — 내 경험에서 시작하는 다음 커리어",
    template: "%s | Career",
  },
  description:
    "GitHub·PDF·Markdown에서 내 기술을 확인하고, 공고와 비교하며 단계별 과제로 다음 커리어를 준비하세요.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} ${careerFont.variable}`}
    >
      <body>
        <CareerProvider>{children}</CareerProvider>
      </body>
    </html>
  );
}
