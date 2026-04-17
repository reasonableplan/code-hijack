import React from "react";
import { useAuth } from "./hooks/useAuth";

export function App() {
  const { user } = useAuth();
  return <div>{user?.name}</div>;
}
