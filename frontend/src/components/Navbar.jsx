
import { Bell, Search } from "lucide-react";
import { useLocation } from "react-router-dom";

const pageInfo = {
  "/": {
    title: "Dashboard",
    description: "Resumen general del seguimiento académico"
  },
  "/tasks": {
    title: "Tareas",
    description: "Consulta y seguimiento de tareas escolares"
  },
  "/deliveries": {
    title: "Entregas",
    description: "Registro y seguimiento de entregas"
  },
  "/alerts": {
    title: "Alertas de riesgo",
    description: "Identificación temprana de posibles retrasos"
  }
};

function Navbar() {
  const location = useLocation();
  const currentPage = pageInfo[location.pathname] || pageInfo["/"];

  return (
    <header className="navbar">
      <div className="navbar-title">
        <h1>{currentPage.title}</h1>
        <p>{currentPage.description}</p>
      </div>

      <div className="navbar-actions">
        <button className="icon-button" aria-label="Buscar">
          <Search size={20} />
        </button>

        <button className="icon-button notification-button"
          aria-label="Notificaciones">
          <Bell size={20} />
          <span className="notification-dot"></span>
        </button>

        <div className="user-profile">
          <div className="user-avatar">AF</div>
          <div className="user-info">
            <strong>Administrador</strong>
            <span>Usuario ATE</span>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Navbar;