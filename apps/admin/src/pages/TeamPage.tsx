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
import { useI18n } from '@/i18n/I18nProvider';

const TeamPage: React.FC = () => {
  const { labelValue, messages } = useI18n();
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
    onError: (cause) => setError(errorMessage(cause, messages.common.requestFailed)),
  });

  const update = async (member: Member, values: Partial<Pick<Member, 'role' | 'status'>>): Promise<void> => {
    setError(null);
    try {
      await api(`/v1/admin/members/${member.id}`, { method: 'PATCH', body: JSON.stringify(values) });
      await queryClient.invalidateQueries({ queryKey: ['members'] });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    }
  };

  return (
    <>
      <PageHeader title={messages.team.title} description={messages.team.description} action={{ label: messages.team.addMember, icon: Plus, onClick: () => setOpen(true) }} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead><TableRow><TableCell>{messages.team.member}</TableCell><TableCell>{messages.common.role}</TableCell><TableCell>{messages.common.status}</TableCell><TableCell align="right">{messages.common.action}</TableCell></TableRow></TableHead>
          <TableBody>
            {data.map((member) => (
              <TableRow key={member.id} hover>
                <TableCell><Typography fontWeight={650}>{member.display_name}</Typography><Typography color="text.secondary" fontSize={12}>{member.email}</Typography></TableCell>
                <TableCell>
                  <Select inputProps={{ 'aria-label': messages.common.role }} size="small" value={member.role} onChange={(event) => void update(member, { role: event.target.value as Member['role'] })} sx={{ minWidth: 150 }}>
                    <MenuItem value="tenant_admin">{messages.team.tenantAdmin}</MenuItem><MenuItem value="agent">{messages.team.agent}</MenuItem>
                  </Select>
                </TableCell>
                <TableCell><Chip size="small" color={member.status === 'active' ? 'success' : 'default'} label={labelValue(member.status)} /></TableCell>
                <TableCell align="right"><Button size="small" color={member.status === 'active' ? 'error' : 'primary'} startIcon={<UserRoundCog size={15} />} onClick={() => void update(member, { status: member.status === 'active' ? 'disabled' : 'active' })}>{member.status === 'active' ? messages.common.disable : messages.common.enable}</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{messages.team.addTeamMember}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label={messages.team.displayName} value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
          <TextField label={messages.common.email} type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <TextField label={messages.team.temporaryPassword} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required helperText={messages.team.passwordHelp} />
          <FormControl><InputLabel>{messages.common.role}</InputLabel><Select label={messages.common.role} value={role} onChange={(event) => setRole(event.target.value as Member['role'])}><MenuItem value="agent">{messages.team.agent}</MenuItem><MenuItem value="tenant_admin">{messages.team.tenantAdmin}</MenuItem></Select></FormControl>
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!displayName.trim() || !email.trim() || password.length < 12 || create.isPending} onClick={() => create.mutate()}>{messages.team.addMember}</Button></DialogActions>
      </Dialog>
    </>
  );
};

export default TeamPage;
