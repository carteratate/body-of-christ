"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { createClient } from "@/lib/supabase/client";

export function LoginForm() {
  const router = useRouter();
  const supabase = createClient();

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY") {
        router.replace("/update-password");
      } else if (session) {
        router.replace("/search");
      }
    });
    return () => subscription.unsubscribe();
  }, [router, supabase]);

  const redirectTo =
    typeof window !== "undefined"
      ? `${window.location.origin}/update-password`
      : undefined;

  return (
    <Auth
      supabaseClient={supabase}
      redirectTo={redirectTo}
      appearance={{
        theme: ThemeSupa,
        variables: {
          default: {
            colors: {
              brand:                        "#C4972A",
              brandAccent:                  "#b38824",
              inputBackground:              "#111829",
              inputText:                    "#EAE6DC",
              inputPlaceholder:             "#7A8099",
              inputBorder:                  "#1C2A40",
              inputBorderFocus:             "#C4972A",
              inputBorderHover:             "#263650",
              defaultButtonBackground:      "#111829",
              defaultButtonBackgroundHover: "#172236",
              defaultButtonBorder:          "#1C2A40",
              defaultButtonText:            "#EAE6DC",
              dividerBackground:            "#1C2A40",
              anchorTextColor:              "#C4972A",
              anchorTextHoverColor:         "#b38824",
              messageText:                  "#EAE6DC",
              messageTextDanger:            "#fca5a5",
              messageBackground:            "#111829",
              messageBackgroundDanger:      "#1C1118",
              messageBorder:                "#1C2A40",
              messageBorderDanger:          "#4a1a1a",
            },
            radii: {
              borderRadiusButton: "6px",
              inputBorderRadius:  "6px",
            },
            fonts: {
              bodyFontFamily:   "inherit",
              buttonFontFamily: "inherit",
            },
          },
        },
      }}
      providers={[]}
    />
  );
}
