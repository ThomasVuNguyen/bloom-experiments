import { LoginGate } from "@/components/login-gate";
import { Chat } from "@/components/chat";

export default function Home() {
  return (
    <LoginGate>
      <Chat />
    </LoginGate>
  );
}
