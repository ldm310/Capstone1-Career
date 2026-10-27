import { Header } from "@/components/layout/header";
import { SignInForm } from "@/components/auth/sign-in-form";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../readability.css";
export default function SignIn() {
  return (
    <div className="feature-site sky-home">
      <Header />
      <main className="feature-content home-width sign-in-main">
        <div className="career-workspace">
          <SignInForm />
        </div>
      </main>
    </div>
  );
}
