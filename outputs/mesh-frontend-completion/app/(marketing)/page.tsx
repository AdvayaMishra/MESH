import { Hero } from "@/components/features/landing/hero";
import { AnalyticsPreview, Faq, FeatureHighlights, FinalCta, Intelligence, Modules, ProductShowcase, RolePreviews, SecurityFirst } from "@/components/features/landing/sections";

export default function LandingPage() {
  return (
    <>
      <Hero />
      <Modules />
      <ProductShowcase />
      <Intelligence />
      <SecurityFirst />
      <RolePreviews />
      <AnalyticsPreview />
      <FeatureHighlights />
      <Faq />
      <FinalCta />
    </>
  );
}
