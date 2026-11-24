import { Header } from "@/components/layout/header";
import { SignInForm } from "@/components/auth/sign-in-form";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../readability.css";
import "../auth.css";
import { pendingKakaoRegistration } from "@/lib/server/kakao-registration";
import { loginDestination } from "@/lib/login-destination";
export default async function SignIn({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; provider?: string; next?: string }>;
}) {
  const params = await searchParams;
  const pending =
    params.provider === "kakao" ? await pendingKakaoRegistration() : null;
  const registration = pending
    ? { email: pending.email, name: pending.name, setup: !!pending.account_id }
    : undefined;
  return (
    <div className="feature-site sky-home">
      <Header />
      <main className="feature-content home-width sign-in-main">
        <div className="career-workspace">
          <SignInForm
            key={
              registration ? registration.email + registration.setup : "normal"
            }
            initialRegistration={registration}
            destination={loginDestination(params.next)}
            initialError={
              params.error ||
              (params.provider === "kakao" && !pending
                ? "kakao_registration_expired"
                : "")
            }
          />
        </div>
      </main>
    </div>
  );
}
