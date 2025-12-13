import { supabase } from '../DB/supabase.js';

export const signUp = async (req, res) => {
    const { email, password, full_name } = req.body;

    const { data, error } = await supabase.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });

  if (error) {
    return res.status(400).json({ error: error.message });
  }

  await supabase.from('users').insert({
    id: data.user.id,
    email,
    full_name,
    role: 'manager', // for now
  });

  return res.status(201).json({
    user: data.user,
  });
}

export const signIn = async (req, res) => {
  const { email, password } = req.body;

  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    return res.status(401).json({ error: error.message });
  }

  return res.json({
    session: data.session,
    user: data.user,
  });
};

export const signOut = async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');

  if (!token) {
    return res.status(401).json({ error: 'Missing token' });
  }

  await supabase.auth.admin.signOut(token);

  return res.json({ message: 'Signed out successfully' });
};