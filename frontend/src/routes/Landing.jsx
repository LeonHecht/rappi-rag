import { Link } from 'react-router-dom';
// import { motion } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

export default function Landing() {
  const { session } = useAuth();
  const user = session?.user;
  const fullName = user?.user_metadata?.full_name;
  const firstName = user?.user_metadata?.first_name || fullName?.split(' ')[0];

  return (
    <div className="h-screen flex flex-col items-center justify-center text-gray-900">
      <div
        // initial={{ y: +30, scale: 1.6 }}
        // animate={{ y: -10, scale: 1 }}
        // transition={{ type: 'spring', stiffness: 80, damping: 16, duration: 1.1 }}
        className="flex items-end"
      >
        <h1 className="text-6xl md:text-6xl font-semibold tracking-tight">
          {user && firstName ? `Hola, ${firstName}` : 'Agentic RAG Template'}
        </h1>
      </div>

      <div
        // initial={{ opacity: 0, y: 20 }}
        // animate={{ opacity: 1, y: 0 }}
        // transition={{ delay: 1.1, duration: 0.5 }}
        className="flex flex-col items-center mt-6 space-y-10"
      >
        <p className="text-xl md:text-2xl font-light text-center">
          Busca documentos, conversa con tu base de conocimiento y sube archivos en un solo lugar
        </p>

        <div className="flex gap-4">
          <Link
            to="/search"
            className="px-8 py-3 bg-black text-white rounded-full hover:bg-gray-800 transition"
          >
            Buscar
          </Link>
          <Link
            to="/chat"
            className="px-8 py-3 bg-gray-200 text-gray-900 rounded-full hover:bg-gray-300 transition"
          >
            Chat
          </Link>
        </div>
      </div>
    </div>
  );
}
