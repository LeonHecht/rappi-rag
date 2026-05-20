import { APP_NAME } from '../config/appConfig';

export default function Navbar() {
  return (
    <nav className="w-full bg-white shadow-sm">
      <div className="w-full flex items-center px-4 py-3 justify-start">
        <span className="text-lg font-semibold tracking-tight text-gray-900">
          {APP_NAME}
        </span>
      </div>
    </nav>
  );
}
