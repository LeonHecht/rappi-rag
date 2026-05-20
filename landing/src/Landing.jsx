import Navbar from './components/Navbar';
import ChatBox from './components/ChatBox';
import { APP_NAME } from './config/appConfig';

export default function Landing() {
  return (
    <div className="relative z-10 flex flex-col min-h-screen">
      <Navbar />

      <main className="flex-1 flex flex-col px-4">
        <section className="flex-1 flex flex-col items-center justify-center">
          <div className="flex flex-col gap-5 max-w-2xl w-full">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-center">
              {APP_NAME}
            </h1>

            <div className="space-y-20">
              <p className="text-center text-sm sm:text-base text-gray-600">
                Busca documentos, chatea con una base de conocimiento y sube archivos en un solo lugar.
              </p>
              <ChatBox
                onSend={() => {
                  const targetUrl = 'https://example.com/gracias';
                  window.location.href = targetUrl;
                }}
              />
            </div>
          </div>
        </section>

        <section className="py-16 space-y-10">
          <div className="max-w-3xl mx-auto text-center text-gray-600 text-sm sm:text-base">
            <p>Seccion para testimonios, ejemplos de uso y caracteristicas del producto.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
