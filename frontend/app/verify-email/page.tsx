import { EmailVerificationForm } from "@/components/auth/email-verification-form";
import { Header } from "@/components/layout/header";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../readability.css";
import "../auth.css";
export const metadata = {
  title: "이메일 인증 | Career",
  referrer: "no-referrer",
};
export default function Page() {
  return (
    <div className="feature-site sky-home">
      <Header />
      <main className="feature-content home-width sign-in-main">
        <div className="career-workspace">
          <EmailVerificationForm />
        </div>
      </main>
    </div>
  );
}
