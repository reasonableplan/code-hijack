import { useState, useEffect } from "react";

export function useAuth() {
  const [user, setUser] = useState<{ name: string } | null>(null);
  useEffect(() => {
    fetch("/api/me").then((r) => r.json()).then(setUser);
  }, []);
  return { user };
}
