/**
 * gauges.js - High-Performance Canvas Radial Gauge Renderer
 * Renders smooth 60FPS futuristic cyber gauge arcs, speed ticks, and neon glow.
 */

class CyberSpeedometer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.currentSpeed = 0;
    this.targetSpeed = 0;
    this.maxSpeed = 240;
    
    // Geometry
    this.centerX = this.canvas.width / 2;
    this.centerY = this.canvas.height / 2 + 15;
    this.radius = 95;
    
    // Angles in radians (from 140 deg to 400 deg)
    this.startAngle = (135 * Math.PI) / 180;
    this.endAngle = (405 * Math.PI) / 180;
    
    this.render();
  }

  setSpeed(speed) {
    this.targetSpeed = Math.max(0, Math.min(this.maxSpeed, speed));
  }

  render() {
    // Smooth lerp interpolation
    this.currentSpeed += (this.targetSpeed - this.currentSpeed) * 0.2;
    
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // 1. Draw Outer Track Background
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, this.radius, this.startAngle, this.endAngle);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 10;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 2. Draw Active Neon Speed Arc
    const speedRatio = Math.min(1.0, this.currentSpeed / this.maxSpeed);
    const currentAngle = this.startAngle + (this.endAngle - this.startAngle) * speedRatio;

    if (speedRatio > 0.005) {
      // Glow filter effect
      ctx.save();
      ctx.beginPath();
      ctx.arc(this.centerX, this.centerY, this.radius, this.startAngle, currentAngle);
      
      const grad = ctx.createLinearGradient(0, 0, this.canvas.width, 0);
      grad.addColorStop(0, '#0088ff');
      grad.addColorStop(0.7, '#00f3ff');
      grad.addColorStop(1, '#10e785');
      
      ctx.strokeStyle = grad;
      ctx.lineWidth = 10;
      ctx.lineCap = 'round';
      ctx.shadowColor = '#00f3ff';
      ctx.shadowBlur = 15;
      ctx.stroke();
      ctx.restore();
    }

    // 3. Draw Radial Tick Marks
    const totalTicks = 24;
    for (let i = 0; i <= totalTicks; i++) {
      const angle = this.startAngle + (this.endAngle - this.startAngle) * (i / totalTicks);
      const isMajor = i % 4 === 0;
      const innerR = isMajor ? this.radius - 22 : this.radius - 16;
      const outerR = this.radius - 10;

      const x1 = this.centerX + Math.cos(angle) * innerR;
      const y1 = this.centerY + Math.sin(angle) * innerR;
      const x2 = this.centerX + Math.cos(angle) * outerR;
      const y2 = this.centerY + Math.sin(angle) * outerR;

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.lineWidth = isMajor ? 2.5 : 1.2;
      ctx.strokeStyle = (i / totalTicks <= speedRatio) ? '#00f3ff' : 'rgba(255, 255, 255, 0.2)';
      ctx.stroke();
    }

    requestAnimationFrame(() => this.render());
  }
}

// Global Speedo Instance
window.CyberSpeedometer = CyberSpeedometer;
