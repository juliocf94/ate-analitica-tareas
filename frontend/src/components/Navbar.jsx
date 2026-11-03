
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  ClipboardList,
  FileCheck,
  BellRing,
  GraduationCap,
  BookOpen
} from "lucide-react";

const menuItems = [
  {
    title: "Dashboard",
    path: "/",
    icon: LayoutDashboard
  },
  {
    title: "Tareas",
    path: "/tasks",
    icon: ClipboardList
  },
  {
    title: "Entregas",
    path: "/deliveries",
    icon: FileCheck
  },
  {
    title: "Alertas de riesgo",
    path: "/alerts",
    icon: BellRing
  }
];

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">
          <GraduationCap size={27} />
        </div>

        <div>
          <h2>ATE</h2>
          <span>Analítica Educativa</span>
        </div>
      </div>

      <div className="sidebar-section">
        <span className="menu-label">MENÚ PRINCIPAL</span>

        <nav className="sidebar-nav">
          {menuItems.map((item) => {
            const Icon = item.icon;

            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  isActive ? "nav-item active" : "nav-item"
                }
              >
                <Icon size={20} />
                <span>{item.title}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div className="sidebar-footer">
        <BookOpen size={19} />
        <div>
          <strong>ATE Educativo</strong>
          <span>Plataforma de seguimiento</span>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
