import { Header } from "@/components/layout/header";
import { AdminSetup } from "@/components/auth/admin-setup";
import "../../sky.css";
import "../../home.css";
import "../../feature-pages.css";
import "../../readability.css";
export default function Page() {
  return (
    <div className="feature-site sky-home">
      <Header />
      <main className="feature-content home-width sign-in-main">
        <div className="career-workspace">
          <AdminSetup />
        </div>
      </main>
    </div>
  );
}
