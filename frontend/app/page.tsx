import { Header } from "@/components/layout/header";
import { SkyExperience } from "@/components/landing/sky-experience";
import { HomeDashboard } from "@/components/home/home-dashboard";
import "./sky.css";
import "./home.css";
import "./feature-pages.css";
import "./dashboard.css";
import "./readability.css";
export default function Home() {
  return (
    <SkyExperience>
      <Header />
      <main>
        <HomeDashboard />
      </main>
      <footer className="home-footer home-width">
        <span>Career</span>
      </footer>
    </SkyExperience>
  );
}
