import { Navigate, Route, Routes } from "react-router-dom";
import { EntryGate } from "./pages/EntryGate";
import { LoginPage } from "./pages/LoginPage";
import { SetupPage } from "./pages/SetupPage";

export default function App() {
  return (
    <div className="app-shell">
      <Routes>
        <Route path="/" element={<EntryGate />} />
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
