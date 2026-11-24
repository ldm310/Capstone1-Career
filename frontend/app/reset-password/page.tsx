import { Header } from "@/components/layout/header";
import { PasswordRecoveryForm } from "@/components/auth/password-recovery-form";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../readability.css";
import "../auth.css";
export const metadata = { referrer: "no-referrer" as const };
export default function Page() {
  return (
    <div className="feature-site sky-home">
      <Header />
      <main className="feature-content home-width sign-in-main">
        <div className="career-workspace">
          <PasswordRecoveryForm reset />
        </div>
      </main>
    </div>
  );
}
