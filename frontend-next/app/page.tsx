import CTA from "@/components/CTA";
import Features from "@/components/Features";
import Footer from "@/components/Footer";
import Hero from "@/components/Hero";
import HowItWorks from "@/components/HowItWorks";
import Navbar from "@/components/Navbar";
import Pricing from "@/components/Pricing";
import Showcase from "@/components/Showcase";
import TemplateMarquee from "@/components/TemplateMarquee";

export default function Home() {
  return (
    <>
      <Navbar />
      <main className="flex-1">
        <Hero />
        <Features />
        <HowItWorks />
        <Showcase />
        <TemplateMarquee />
        <Pricing />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
