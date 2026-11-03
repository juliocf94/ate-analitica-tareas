
import {
    ClipboardList,
    Clock,
    CheckCircle,
    AlertTriangle,
    ArrowRight,
    CalendarDays
  } from "lucide-react";
  
  import { Link } from "react-router-dom";
  import StatCard from "../components/StatCard";
  
  const statistics = [
    {
      title: "Total de tareas",
      value: "248",
      description: "Tareas registradas",
      icon: ClipboardList,
      color: "blue"
    },
    {
      title: "Pendientes",
      value: "64",
      description: "Esperando entrega",
      icon: Clock,
      color: "orange"
    },
    {
      title: "Entregadas",
      value: "162",
      description: "Tareas completadas",
      icon: CheckCircle,
      color: "green"
    },
    {
      title: "En riesgo",
      value: "22",
      description: "Posibles retrasos",
      icon: AlertTriangle,
      color: "red"
    }
  ];
  
  const recentTasks = [
    {
      id: 1,
      student: "20260001",
      task: "Investigación sobre ecosistemas",
      subject: "Ciencias Naturales",
      deadline: "04 Nov 2026",
      status: "Pendiente",
      risk: "Bajo"
    },
    {
      id: 2,
      student: "20260002",
      task: "Ejercicios de álgebra",
      subject: "Matemáticas",
      deadline: "03 Nov 2026",
      status: "Pendiente",
      risk: "Alto"
    },
    {
      id: 3,
      student: "20260003",
      task: "Lectura y análisis literario",
      subject: "Lenguaje",
      deadline: "05 Nov 2026",
      status: "Entregada",
      risk: "Bajo"
    },
    {
      id: 4,
      student: "20260004",
      task: "Exposición de historia",
      subject: "Estudios Sociales",
      deadline: "02 Nov 2026",
      status: "Pendiente",
      risk: "Alto"
    }
  ];
  
  function Dashboard() {
    return (
      <div className="dashboard">
  
        {/* Bienvenida */}
        <section className="welcome-section">
          <div>
            <span className="welcome-label">
              PLATAFORMA EDUCATIVA ATE
            </span>
  
            <h2>¡Bienvenido a ATE!</h2>
  
            <p>
              Consulta el progreso académico y detecta
              posibles retrasos en las entregas escolares.
            </p>
          </div>
  
          <div className="welcome-icon">
            <CalendarDays size={55} />
          </div>
        </section>
  
        {/* Estadísticas */}
        <section className="stats-grid">
          {statistics.map((stat) => (
            <StatCard
              key={stat.title}
              {...stat}
            />
          ))}
        </section>
  
        {/* Contenido principal */}
        <section className="dashboard-grid">
  
          {/* Tabla de tareas */}
          <div className="content-card tasks-card">
  
            <div className="card-header">
              <div>
                <h3>Tareas recientes</h3>
                <p>Resumen de las últimas actividades registradas</p>
              </div>
  
              <Link to="/tasks" className="text-link">
                Ver todas <ArrowRight size={16} />
              </Link>
            </div>
  
            <div className="table-container">
              <table className="tasks-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Tarea</th>
                    <th>Fecha límite</th>
                    <th>Estado</th>
                    <th>Riesgo</th>
                  </tr>
                </thead>
  
                <tbody>
                  {recentTasks.map((task) => (
                    <tr key={task.id}>
                      <td>
                        <strong>{task.student}</strong>
                      </td>
  
                      <td>
                        <div className="task-name">
                          <strong>{task.task}</strong>
                          <span>{task.subject}</span>
                        </div>
                      </td>
  
                      <td>{task.deadline}</td>
  
                      <td>
                        <span className={`status-badge ${
                          task.status === "Entregada"
                            ? "status-completed"
                            : "status-pending"
                        }`}>
                          {task.status}
                        </span>
                      </td>
  
                      <td>
                        <span className={`risk-badge ${
                          task.risk === "Alto"
                            ? "risk-high"
                            : "risk-low"
                        }`}>
                          {task.risk}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
  
          {/* Alertas */}
          <div className="content-card alerts-card">
  
            <div className="card-header">
              <div>
                <h3>Alertas importantes</h3>
                <p>Seguimiento de posibles retrasos</p>
              </div>
            </div>
  
            <div className="alert-item">
              <div className="alert-icon high">
                <AlertTriangle size={20} />
              </div>
  
              <div className="alert-content">
                <strong>Riesgo alto de retraso</strong>
                <p>
                  Ejercicios de álgebra - Estudiante 20260002
                </p>
                <span>Fecha límite: 03 Nov 2026</span>
              </div>
            </div>
  
            <div className="alert-item">
              <div className="alert-icon high">
                <AlertTriangle size={20} />
              </div>
  
              <div className="alert-content">
                <strong>Entrega próxima con riesgo</strong>
                <p>
                  Exposición de historia - Estudiante 20260004
                </p>
                <span>Fecha límite: 02 Nov 2026</span>
              </div>
            </div>
  
            <Link to="/alerts" className="alerts-link">
              Consultar todas las alertas
              <ArrowRight size={16} />
            </Link>
  
          </div>
        </section>
  
        <footer className="dashboard-footer">
          ATE — Analítica de Tareas Educativas
          <span>Datos demostrativos para el desarrollo del Sprint 2</span>
        </footer>
  
      </div>
    );
  }
  
  export default Dashboard;
  