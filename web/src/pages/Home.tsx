import { Terminal, Database, LineChart, Zap, ChevronRight, Github } from 'lucide-react';
import './Home.css';

export function Home() {
    return (
        <div className="home-page">
            {/* Hero Section */}
            <section className="hero-section container">
                <div className="hero-content animate-fade-in">
                    <div className="badge glass-panel">
                        <span className="badge-dot"></span>
                        ATS Core Engine v1.0
                    </div>

                    <h1 className="hero-title">
                        Next-Generation <br />
                        <span className="text-gradient">Automated Trading</span> System
                    </h1>

                    <p className="hero-subtitle">
                        A comprehensive theoretical and practical framework for algorithmic trading across stocks, futures, and options markets. Built for performance, scalability, and precision.
                    </p>

                    <div className="hero-actions">
                        <button className="btn-primary btn-lg">
                            Explore Theory <ChevronRight size={18} />
                        </button>
                        <button className="btn-secondary btn-lg">
                            <Github size={18} /> View Source
                        </button>
                    </div>
                </div>

                <div className="hero-visual animate-float">
                    <div className="visual-core glass-panel">
                        {/* Abstract representation of trading dashboard */}
                        <div className="visual-header">
                            <div className="visual-dots">
                                <span></span><span></span><span></span>
                            </div>
                            <div className="visual-title">ATS Dashboard / Live</div>
                        </div>

                        <div className="visual-body">
                            <div className="visual-chart">
                                <div className="chart-line"></div>
                                <div className="chart-glow"></div>
                            </div>

                            <div className="visual-metrics">
                                <div className="metric-card">
                                    <div className="metric-label">Win Rate</div>
                                    <div className="metric-value text-gradient">68.4%</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">Alpha</div>
                                    <div className="metric-value text-gradient-warm">+12.8%</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features Section */}
            <section className="features-section container">
                <div className="section-header">
                    <h2 className="section-title">System Architecture</h2>
                    <p className="section-subtitle">Scalable, low-latency infrastructure designed for high-frequency data processing.</p>
                </div>

                <div className="features-grid">
                    <div className="feature-card glass-panel">
                        <div className="feature-icon">
                            <LineChart size={24} className="text-gradient" />
                        </div>
                        <h3 className="feature-title">Quantitative Strategies</h3>
                        <p className="feature-desc">Machine learning and statistical arbitrage models optimized for futures and options.</p>
                    </div>

                    <div className="feature-card glass-panel">
                        <div className="feature-icon">
                            <Database size={24} className="text-gradient" />
                        </div>
                        <h3 className="feature-title">Data Pipeline</h3>
                        <p className="feature-desc">Real-time market data ingestion and normalized historical data storage.</p>
                    </div>

                    <div className="feature-card glass-panel">
                        <div className="feature-icon">
                            <Zap size={24} className="text-gradient" />
                        </div>
                        <h3 className="feature-title">Order Execution</h3>
                        <p className="feature-desc">Low-latency routing and execution algorithms to minimize slippage.</p>
                    </div>

                    <div className="feature-card glass-panel">
                        <div className="feature-icon">
                            <Terminal size={24} className="text-gradient" />
                        </div>
                        <h3 className="feature-title">Risk Management</h3>
                        <p className="feature-desc">Real-time exposure monitoring and automated position sizing.</p>
                    </div>
                </div>
            </section>
        </div>
    );
}
