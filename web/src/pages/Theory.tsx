import { Book, Code, Calculator, TrendingUp } from 'lucide-react';
import './Theory.css';

export function Theory() {
    return (
        <div className="theory-page container">
            <aside className="theory-sidebar glass-panel">
                <div className="sidebar-group">
                    <h4 className="group-title">Getting Started</h4>
                    <ul className="group-list">
                        <li><a href="#" className="active">Introduction</a></li>
                        <li><a href="#">System Architecture</a></li>
                        <li><a href="#">Setup Guide</a></li>
                    </ul>
                </div>

                <div className="sidebar-group">
                    <h4 className="group-title">Core Concepts</h4>
                    <ul className="group-list">
                        <li><a href="#">Market Data Handling</a></li>
                        <li><a href="#">Order Execution</a></li>
                        <li><a href="#">Risk Management</a></li>
                    </ul>
                </div>

                <div className="sidebar-group">
                    <h4 className="group-title">Strategies</h4>
                    <ul className="group-list">
                        <li><a href="#">Options Pricing Models</a></li>
                        <li><a href="#">Statistical Arbitrage</a></li>
                        <li><a href="#">Trend Following</a></li>
                    </ul>
                </div>
            </aside>

            <main className="theory-content">
                <div className="content-header">
                    <div className="breadcrumb">Docs / Getting Started / Introduction</div>
                    <h1>ATS Theory & Documentation</h1>
                    <p className="lead-text">
                        Welcome to the official documentation for the ATS (Automated Trading System). This resource covers the underlying financial theories, system architecture, and practical implementation details.
                    </p>
                </div>

                <div className="content-cards">
                    <div className="doc-card glass-panel">
                        <Book className="doc-icon text-gradient" size={32} />
                        <h3>Theoretical Foundations</h3>
                        <p>Explore the mathematical models for options pricing, including Black-Scholes and Binomial Option Pricing Models.</p>
                    </div>

                    <div className="doc-card glass-panel">
                        <Code className="doc-icon text-gradient" size={32} />
                        <h3>Implementation Guide</h3>
                        <p>Navigate the codebase structure, understand data pipelines, and learn how to implement custom algorithms.</p>
                    </div>

                    <div className="doc-card glass-panel">
                        <Calculator className="doc-icon text-gradient" size={32} />
                        <h3>Risk Models</h3>
                        <p>Dive into Value at Risk (VaR), portfolio beta calculation, and automated hedging strategies.</p>
                    </div>

                    <div className="doc-card glass-panel">
                        <TrendingUp className="doc-icon text-gradient" size={32} />
                        <h3>Backtesting Engine</h3>
                        <p>Learn how to simulate trading strategies against historical market data with realistic slippage and commission.</p>
                    </div>
                </div>
            </main>
        </div>
    );
}
