import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import { Shield, Loader2 } from 'lucide-react';
import clsx from 'clsx';

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await axios.post('/api/auth/register', {
        email,
        password,
        name
      });
      // On success, redirect to login
      navigate('/login');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 relative overflow-hidden">
      {/* Background decorations */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
        <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-primary/5 blur-[120px]" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-accent/5 blur-[120px]" />
      </div>

      <div className="w-full max-w-[400px] z-10 animate-fade-in">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-6">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-surface to-surface-hover border border-border flex items-center justify-center shadow-sm">
              <Shield className="w-6 h-6 text-text-primary" />
            </div>
          </div>
          <h2 className="text-[24px] font-semibold text-text-primary tracking-tight">Create an Account</h2>
          <p className="text-[14px] text-text-secondary mt-2">Start building your AI trading portfolio.</p>
        </div>

        <div className="card p-8 shadow-2xl border-border-bright bg-surface/80 backdrop-blur-xl">
          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-danger/10 border border-danger/20 text-danger text-[13px] font-medium p-3 rounded-lg flex items-start gap-2">
                <div className="mt-0.5">⚠️</div>
                <p>{error}</p>
              </div>
            )}
            
            <div className="space-y-4">
              <div>
                <label className="block text-[13px] font-medium text-text-secondary mb-1.5">Full Name</label>
                <input
                  type="text"
                  required
                  className="input-field py-2.5 px-3.5 text-[14px]"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

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
                  minLength={6}
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
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Register'}
            </button>
          </form>
        </div>

        <p className="text-center text-[13px] text-text-secondary mt-8">
          Already have an account?{' '}
          <Link to="/login" className="text-primary hover:text-primary-hover font-semibold transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
