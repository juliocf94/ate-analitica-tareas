
function StatCard({ title, value, description, icon: Icon, color }) {
    return (
      <article className="stat-card">
        <div className={`stat-icon ${color}`}>
          <Icon size={23} />
        </div>
  
        <div className="stat-content">
          <span className="stat-title">{title}</span>
          <h2>{value}</h2>
          <p>{description}</p>
        </div>
      </article>
    );
  }
  
  export default StatCard;
  