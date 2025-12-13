import { Router } from 'express';

const scheduleRouter = Router();

scheduleRouter.get('/schedules?week=YYYY-MM-DD', (req, res) => {
    res.send('GET schedules for the week' );
});
scheduleRouter.get('/schedules/month?month=YYYY-MM', (req, res) => {
    res.send('GET schedules for the month');
});

scheduleRouter.post('/', (req, res) => {
    res.send('CREATE new schedule');
});

scheduleRouter.put('/:id', (req, res) => {
    res.send('UPDATE schedule details');
});

export default scheduleRouter;