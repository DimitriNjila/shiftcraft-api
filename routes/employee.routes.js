import { Router } from 'express';

const employeeRouter = Router();

employeeRouter.get('/', (req, res) => {
    res.send('GET all employees');
});
employeeRouter.get('/:id', (req, res) => {
    res.send('GET employee details');
});

employeeRouter.post('/', (req, res) => {
    res.send('CREATE new employee');
});

employeeRouter.put('/:id', (req, res) => {
    res.send('UPDATE employee details');
});

employeeRouter.delete('/:id', (req, res) => {
    res.send('DELETE employee');
});

export default employeeRouter;