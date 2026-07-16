import { Plus, UserRoundCog } from 'lucide-react';
import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type { Member } from '@/api/types';
import PageHeader from '@/components/PageHeader';

const TeamPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { data } = useSuspenseQuery({
    queryKey: ['members'],
    queryFn: () => api<Member[]>('/v1/admin/members'),
  });
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Member['role']>('agent');
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api<Member>('/v1/admin/members', {
      method: 'POST',
      body: JSON.stringify({ email, display_name: displayName, temporary_password: password, role }),
    }),
    onSuccess: async () => {
      setOpen(false);
      setEmail('');
      setDisplayName('');
      setPassword('');
      await queryClient.invalidateQueries({ queryKey: ['members'] });
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  const update = async (member: Member, values: Partial<Pick<Member, 'role' | 'status'>>): Promise<void> => {
    setError(null);
    try {
      await api(`/v1/admin/members/${member.id}`, { method: 'PATCH', body: JSON.stringify(values) });
      await queryClient.invalidateQueries({ queryKey: ['members'] });
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  return (
    <>
      <PageHeader title="Team" description="Tenant administrators and human support agents." action={{ label: 'Add member', icon: Plus, onClick: () => setOpen(true) }} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead><TableRow><TableCell>Member</TableCell><TableCell>Role</TableCell><TableCell>Status</TableCell><TableCell align="right">Action</TableCell></TableRow></TableHead>
          <TableBody>
            {data.map((member) => (
              <TableRow key={member.id} hover>
                <TableCell><Typography fontWeight={650}>{member.display_name}</Typography><Typography color="text.secondary" fontSize={12}>{member.email}</Typography></TableCell>
                <TableCell>
                  <Select size="small" value={member.role} onChange={(event) => void update(member, { role: event.target.value as Member['role'] })} sx={{ minWidth: 150 }}>
                    <MenuItem value="tenant_admin">Tenant admin</MenuItem><MenuItem value="agent">Agent</MenuItem>
                  </Select>
                </TableCell>
                <TableCell><Chip size="small" color={member.status === 'active' ? 'success' : 'default'} label={member.status} /></TableCell>
                <TableCell align="right"><Button size="small" color={member.status === 'active' ? 'error' : 'primary'} startIcon={<UserRoundCog size={15} />} onClick={() => void update(member, { status: member.status === 'active' ? 'disabled' : 'active' })}>{member.status === 'active' ? 'Disable' : 'Enable'}</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add team member</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label="Display name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
          <TextField label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <TextField label="Temporary password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required helperText="At least 12 characters" />
          <FormControl><InputLabel>Role</InputLabel><Select label="Role" value={role} onChange={(event) => setRole(event.target.value as Member['role'])}><MenuItem value="agent">Agent</MenuItem><MenuItem value="tenant_admin">Tenant admin</MenuItem></Select></FormControl>
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="contained" disabled={!displayName.trim() || !email.trim() || password.length < 12 || create.isPending} onClick={() => create.mutate()}>Add member</Button></DialogActions>
      </Dialog>
    </>
  );
};

export default TeamPage;
