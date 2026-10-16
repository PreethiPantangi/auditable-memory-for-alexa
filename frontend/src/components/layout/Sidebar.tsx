import { MessageCircle, Database, LogOut /**, ChefHat**/ } from "lucide-react";

import AlexaPlusLogo from "../branding/AlexaPlusLogo";
import { logoutDemo } from "../../services/demoAuthApi";

export type AppPage = "chat" | "memories" | "insights";

const navItems = [
  {
    label: "Chat",
    id: "chat",
    icon: MessageCircle,
  },
  {
    label: "Memories",
    id: "memories",
    icon: Database,
  },
  // ,
  // {
  //   label: "Cooking Insights",
  //   id: "insights",
  //   icon: ChefHat,
  // },
] as const;

interface SidebarProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
  onLogout: () => void;
}

export default function Sidebar({
  activePage,
  onNavigate,
  onLogout,
}: SidebarProps) {
  async function handleLogout() {
    try {
      await logoutDemo();
      onLogout();
    } catch (error) {
      console.error("Logout failed:", error);
    }
  }

  return (
    <aside className="border-r border-slate-200 bg-white">
      <div className="flex h-full flex-col">
        <div className="border-b border-slate-100 px-6 py-6">
          <AlexaPlusLogo />
        </div>

        <nav className="flex-1 px-4 py-5">
          <ul className="space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activePage === item.id;

              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onNavigate(item.id)}
                    aria-current={isActive ? "page" : undefined}
                    className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-base font-medium transition ${
                      isActive
                        ? "bg-blue-50 text-blue-700"
                        : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <Icon size={20} className="shrink-0" />
                    <span>{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <button
          type="button"
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600"
        >
          <LogOut size={18} aria-hidden="true" />
          <span>Log out</span>
        </button>
      </div>
    </aside>
  );
}
