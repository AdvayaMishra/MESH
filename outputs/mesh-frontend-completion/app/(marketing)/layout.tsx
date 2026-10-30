import { MarketingFooter, MarketingNav } from "@/components/features/landing/nav-footer";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2">Skip to content</a>
      <MarketingNav />
      <main id="main">{children}</main>
      <MarketingFooter />
    </>
  );
}
