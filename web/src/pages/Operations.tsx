import { SystemStatusBar } from '../components/operations/SystemStatusBar';
import { PositionTable } from '../components/operations/PositionTable';
import { SignalList } from '../components/operations/SignalList';
import { OrderLog } from '../components/operations/OrderLog';
import './Operations.css';

export function Operations() {
    return (
        <div className="operations-page container">
            <SystemStatusBar />

            <div className="operations-header">
                <h1 className="page-title">Trading Operations</h1>
                <p className="page-subtitle">실시간 포지션 관리 및 주문 모니터링</p>
            </div>

            <div className="operations-grid">
                <div className="operations-main">
                    <PositionTable />
                </div>
                <div className="operations-side">
                    <SignalList />
                </div>
            </div>

            <OrderLog />
        </div>
    );
}
