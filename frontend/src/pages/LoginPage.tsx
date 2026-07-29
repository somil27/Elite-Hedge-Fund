import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../store/api';
import { useAuthStore } from '../store/authStore';
import { Briefcase, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import GoogleLoginButton from '../components/auth/GoogleLoginButton';

export default function LoginPage() {
  const [email, setEmail] = useState('test@example.com'); // Default for easy testing
  const [password, setPassword] = useState('password123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);
  const fetchUser = useAuthStore((s) => s.fetchUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // OAuth2 requires form data (URL encoded), not JSON
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      const res = await api.post('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });

      setToken(res.data.access_token);
      await fetchUser(); // Load user profile
      navigate('/'); // Go to dashboard
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 relative overflow-hidden">
      {/* Background decorations */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/5 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-accent/5 blur-[120px]" />
      </div>

      <div className="w-full max-w-[400px] z-10 animate-fade-in">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-6">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20 flex items-center justify-center shadow-glow">
              <Briefcase className="w-6 h-6 text-primary" />
            </div>
          </div>
          <h2 className="text-[24px] font-semibold text-text-primary tracking-tight">Sign in to AlphaDesk</h2>
          <p className="text-[14px] text-text-secondary mt-2">Welcome back! Please enter your details.</p>
        </div>

        <div className="card p-8 shadow-2xl border-border-bright bg-surface/80 backdrop-blur-xl">
          <GoogleLoginButton />
          
          <div className="relative flex items-center py-5">
            <div className="flex-grow border-t border-[#333333]"></div>
            <span className="flex-shrink-0 mx-4 text-text-secondary text-[12px] uppercase font-medium">Or continue with email</span>
            <div className="flex-grow border-t border-[#333333]"></div>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-danger/10 border border-danger/20 text-danger text-[13px] font-medium p-3 rounded-lg flex items-start gap-2">
                <div className="mt-0.5">⚠️</div>
                <p>{error}</p>
              </div>
            )}
            
            <div className="space-y-4">
              <div>
                <label className="block text-[13px] font-medium text-text-secondary mb-1.5">Email</label>
                <input
                  type="email"
                  required
                  className="input-field py-2.5 px-3.5 text-[14px]"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              
              <div>
                <label className="block text-[13px] font-medium text-text-secondary mb-1.5">Password</label>
                <input
                  type="password"
                  required
                  className="input-field py-2.5 px-3.5 text-[14px] tracking-widest"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full h-11 flex justify-center items-center text-[14px] font-semibold mt-2 shadow-glow"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-[13px] text-text-secondary mt-8">
          Don't have an account?{' '}
          <Link to="/register" className="text-primary hover:text-primary-hover font-semibold transition-colors">
            Register here
          </Link>
        </p>
      </div>
    </div>
  );
}
