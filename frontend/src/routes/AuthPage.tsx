import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "@/context/AuthContext";
import SignUpForm from "@/components/SignUpForm";
import SignInForm from "@/components/SignInForm";
import { isDemoMode } from "@/lib/demoMode";

export default function AuthPage() {
  const navigate = useNavigate();
  const { session } = useAuth();
  const [view, setView] = useState<"sign_in" | "sign_up">("sign_in");
  const [sharedEmail, setSharedEmail] = useState("");
  const [sharedPassword, setSharedPassword] = useState("");

  useEffect(() => {
    // Redirect to home if user is already authenticated
    if (session || isDemoMode) {
      navigate("/");
    }
  }, [session, navigate]);

  if (isDemoMode) return null;

  return (
    <div className="flex justify-center items-center h-screen bg-gray-50">
      {view === "sign_in" ? (
        <SignInForm 
          onSwitchToSignUp={() => setView("sign_up")}
          email={sharedEmail}
          setEmail={setSharedEmail}
          password={sharedPassword}
          setPassword={setSharedPassword}
        />
      ) : (
        <SignUpForm 
          onSwitchToSignIn={() => setView("sign_in")}
          email={sharedEmail}
          setEmail={setSharedEmail}
          password={sharedPassword}
          setPassword={setSharedPassword}
        />
      )}
    </div>
  );
}
