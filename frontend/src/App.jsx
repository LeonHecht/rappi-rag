import { Routes, Route } from "react-router-dom";
import Navbar from './components/Navbar';
import Landing from "./routes/Landing";
import Search from "./routes/Search";
import Chat from "./routes/Chat";
import Uploads from "./routes/Uploads";
import AuthPage from "./routes/AuthPage";

export default function App() {
  return (
    <div className="flex flex-col h-dvh overflow-x-hidden">
      <Navbar />
      <main className="flex flex-col flex-1 min-h-0 bg-[#F5F5F7]">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/search" element={<Search />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/uploads" element={<Uploads />} />
          <Route path="/login" element={<AuthPage />} />
        </Routes>
      </main>
    </div>
  );
}
