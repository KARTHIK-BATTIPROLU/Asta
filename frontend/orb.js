// ASTA Blue Orb Visuals (Three.js)

class AstaOrb {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        
        // Scene setup
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, this.container.clientWidth / this.container.clientHeight, 0.1, 1000);
        this.camera.position.z = 5;
        
        this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.container.appendChild(this.renderer.domElement);
        
        // Orb Core
        const geometry = new THREE.SphereGeometry(2, 64, 64);
        
        // Shader Material for the breathing/swirling glow
        this.uniforms = {
            time: { value: 0 },
            baseColor: { value: new THREE.Color("#1e90ff") },
            glowColor: { value: new THREE.Color("#7fd4ff") },
            pulseAmplitude: { value: 0.1 },
            pulseSpeed: { value: 1.0 },
            swirlSpeed: { value: 0.0 }
        };
        
        this.material = new THREE.ShaderMaterial({
            uniforms: this.uniforms,
            vertexShader: `
                uniform float time;
                uniform float pulseAmplitude;
                uniform float pulseSpeed;
                varying vec2 vUv;
                varying vec3 vNormal;
                
                void main() {
                    vUv = uv;
                    vNormal = normalize(normalMatrix * normal);
                    
                    // Basic breathing pulse
                    float pulse = sin(time * pulseSpeed) * pulseAmplitude;
                    vec3 newPosition = position + normal * pulse;
                    
                    gl_Position = projectionMatrix * modelViewMatrix * vec4(newPosition, 1.0);
                }
            `,
            fragmentShader: `
                uniform vec3 baseColor;
                uniform vec3 glowColor;
                uniform float time;
                uniform float swirlSpeed;
                varying vec2 vUv;
                varying vec3 vNormal;
                
                void main() {
                    // Fresnel glow effect
                    float intensity = pow(0.7 - dot(vNormal, vec3(0, 0, 1.0)), 2.0);
                    
                    // Swirl effect
                    float swirl = sin(vUv.y * 10.0 + time * swirlSpeed) * 0.5 + 0.5;
                    
                    vec3 finalColor = mix(baseColor, glowColor, intensity + swirl * 0.3);
                    
                    gl_FragColor = vec4(finalColor, 0.8 + intensity * 0.2);
                }
            `,
            transparent: true,
            blending: THREE.AdditiveBlending
        });
        
        this.orb = new THREE.Mesh(geometry, this.material);
        this.scene.add(this.orb);
        
        // Resize handler
        window.addEventListener('resize', this.onWindowResize.bind(this), false);
        
        // Animation loop
        this.clock = new THREE.Clock();
        this.animate = this.animate.bind(this);
        this.animate();
        
        // Initial state
        this.setState('idle');
    }
    
    setState(state) {
        console.log(`[Orb] State changed to: ${state}`);
        switch(state) {
            case 'idle':
                // slow dim breathing
                this.uniforms.pulseAmplitude.value = 0.05;
                this.uniforms.pulseSpeed.value = 1.0;
                this.uniforms.swirlSpeed.value = 0.5;
                this.orb.scale.set(1, 1, 1);
                this.uniforms.baseColor.value.set("#104e8b"); // dimmer blue
                break;
            case 'listening':
                // brighten + expand
                this.uniforms.pulseAmplitude.value = 0.02;
                this.uniforms.pulseSpeed.value = 2.0;
                this.uniforms.swirlSpeed.value = 1.0;
                this.orb.scale.set(1.2, 1.2, 1.2);
                this.uniforms.baseColor.value.set("#1e90ff"); // bright blue
                break;
            case 'thinking':
                // fast inner swirl
                this.uniforms.pulseAmplitude.value = 0.05;
                this.uniforms.pulseSpeed.value = 1.0;
                this.uniforms.swirlSpeed.value = 10.0;
                this.orb.scale.set(1, 1, 1);
                this.uniforms.baseColor.value.set("#4169e1"); // deeper royal blue
                break;
            case 'speaking':
                // pulse with amplitude (simulated here since we don't have direct audio volume)
                this.uniforms.pulseAmplitude.value = 0.2;
                this.uniforms.pulseSpeed.value = 8.0;
                this.uniforms.swirlSpeed.value = 2.0;
                this.orb.scale.set(1.1, 1.1, 1.1);
                this.uniforms.baseColor.value.set("#7fd4ff"); // very bright
                break;
        }
    }
    
    onWindowResize() {
        this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    }
    
    animate() {
        requestAnimationFrame(this.animate);
        this.uniforms.time.value = this.clock.getElapsedTime();
        this.orb.rotation.y += 0.005;
        this.renderer.render(this.scene, this.camera);
    }
}

// Global instance
let orb;
window.addEventListener('DOMContentLoaded', () => {
    orb = new AstaOrb('orb-container');
});
