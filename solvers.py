import pycuda.driver as cuda
import numpy as np
import integrator.symp_integrator as si
import postprocess.procedures as pp

from lattice import *

"""
####################################################################
# Homogeneous evolution solver
####################################################################
"""

def run_hom(lat, V, sim, evo, postp, model, start, end, data_path, order = 4):

    start.record()

    data_folder = make_subdir(data_path, 'homog')
        
    solve_hom(lat, V, sim, evo, postp, model, data_folder,
            order)

    write_csv(lat, data_folder, mode = 'homog')

    "Synchronize:"
    end.record()
    end.synchronize()


def solve_hom(lat, V, sim, evo, postp, model, path, order = 4):
    """Solve homogeneous background evolution with an integrator of
    a given order (=4 by default)."""

    if order == 2:
        while (sim.t_hom<model.t_fin_hom):
            if (sim.i0_hom%(model.flush_freq_hom)==0):
                evo.calc_rho_pres_hom(lat, V, sim, print_Q = True)
                sim.flush_hom(lat, path)

            sim.i0_hom += 1
            evo.evo_step_bg_2(lat, V, sim, lat.dtau_hom/sim.a_hom)

    elif order == 4:
        while (sim.t_hom<model.t_fin_hom):
            if (sim.i0_hom%(model.flush_freq_hom)==0):
                evo.calc_rho_pres_hom(lat, V, sim, print_Q = True)
                sim.flush_hom(lat, path)

            sim.i0_hom += 1
            evo.evo_step_bg_4(lat, V, sim, lat.dtau_hom/sim.a_hom)

    elif order == 6:
        while (sim.t_hom<model.t_fin_hom):
            if (sim.i0_hom%(model.flush_freq_hom)==0):
                evo.calc_rho_pres_hom(lat, V, sim, print_Q = True)
                sim.flush_hom(lat, path)

            sim.i0_hom += 1
            evo.evo_step_bg_6(lat, V, sim, lat.dtau_hom/sim.a_hom)
        
    elif order == 8:
        while (sim.t_hom<model.t_fin_hom):
            if (sim.i0_hom%(model.flush_freq_hom)==0):
                evo.calc_rho_pres_hom(lat, V, sim, print_Q = True)
                sim.flush_hom(lat, path)

            sim.i0_hom += 1
            evo.evo_step_bg_8(lat, V, sim, lat.dtau_hom/sim.a_hom)

"""
####################################################################
# Non-homogeneous evolution
####################################################################
"""

def reinit(lat, V, sim, evo, model, a_in, fields0, pis0):
    "This function will re-initialize the system:"
    sim.reinit(model, lat, V, a_in, fields0, pis0)
    evo.update(lat, sim)
    sim.flush_freq = model.flush_freq
    sim.adjust_fields(lat)
    "Adjust p:"
    evo.calc_rho_pres(lat, V, sim, print_Q = False, print_w=False, flush=False)
    sim.adjust_p(lat)


def run_non_linear(lat, V, sim, evo, postp, model, start, end, data_path,
                   order = 4, endQ = 'time', print_Q = True,
                   print_w = False):

        start.record()

        i0_sum = 0

        path_list = []

        for i in xrange(1,model.sim_num+1):
            print '\nSimulation run: ', i

            data_folder = make_subdir(data_path, sim_number=i)
            path_list.append(data_folder)

            """Solve background and linearized perturbations if necessary
               (This has not been tested thoroughly!):"""
            if model.lin_evo:
                print '\nLinearized simulatios:\n'

                "Save initial data:"
                evo.calc_rho_pres(lat, V, sim, print_Q, print_w)

                "Go to Fourier space:"
                evo.x_to_k_space(lat, sim, perturb=True)
                evo.update(lat, sim)

                while sim.a < model.a_limit:
                    "Evolve all the k-modes coefficients:"
                    evo.lin_evo_step(lat, V, sim)
                    "Evolve perturbations:"
                    evo.transform(lat, sim)
                    evo.calc_rho_pres_back(lat, V, sim, print_Q)
                    i0_sum += sim.steps


                "Go back to position space:"
                evo.k_to_x_space(lat, sim, unperturb=True)
                sim.adjust_fields(lat)



            print '\nNon-linear simulation:\n'

            "Solve non-linear equations:"
            solve_non_linear(lat, V, sim, evo, postp, model, data_folder,
                             order, endQ, print_Q, print_w)
            
            evo.calc_rho_pres(lat, V, sim, print_Q)
            data_file = sim.flush(lat, path = data_folder, save_evo = False)

            i0_sum += sim.i0

            if model.zetaQ:

                #These might have to be edited for different models:"
                "Calculate ln(a) and omega_curv at H_ref:"
                ln_a = np.interp(-np.log(model.H_ref),-np.log(sim.flush_H),
                                 np.log(sim.flush_a))
                r = np.interp(-np.log(model.H_ref),-np.log(sim.flush_H),
                              sim.fields[0].omega_list)

                "Write these into a csv file:"
                zeta_res = np.array([sim.fields[0].f0_in,model.H_ref,ln_a,r])

                write_zeta_result(data_path, zeta_res)

            "Calculate spectrums and statistics:"
            if lat.postQ:
                postp.process_fields(lat, V, sim, data_file)

            "Re-initialize system:"
            if model.sim_num > 1 and i < model.sim_num:
                sim.reinit(model, lat, V, model.a_in, sim.fields0, sim.pis0)
                evo.update(lat, sim)
                sim.flush_freq = model.flush_freq
                sim.adjust_fields(lat)
                "Adjust p:"
                evo.calc_rho_pres(lat, V, sim, print_Q, print_w, flush=False)
                sim.adjust_p(lat)

        "Synchronize:"
        end.record()
        end.synchronize()

        sim.time_sim = end.time_since(start)*1e-3
        sim.per_stp = sim.time_sim/i0_sum

        if model.csvQ:
            for path in path_list:
                write_csv(lat, path)

def solve_non_linear(lat, V, sim, evo, postp, model, path, order = 4,
                     endQ = 'time', print_Q = True, print_w = False):
    """This will solve the non-linear evolution of the system with
       an integrator of a given order:"""

    if endQ == 'time':

        if order == 2:
            "Solve the non-linear evolution:"
            while (sim.t<model.t_fin):
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_2(lat, V, sim, lat.dtau)

        elif order == 4:
            "Solve the non-linear evolution:"
            while (sim.t<model.t_fin):
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_4(lat, V, sim, lat.dtau)

        elif order == 6:
            "Solve the non-linear evolution:"
            while (sim.t<model.t_fin):
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_6(lat, V, sim, lat.dtau)

        elif order == 8:
            "Solve the non-linear evolution:"
            while (sim.t<model.t_fin):
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_8(lat, V, sim, lat.dtau)

    elif endQ == 'H':
        
        if order == 2:
            "Solve the non-linear evolution:"
            while (sim.H > 0.99*model.H_ref):
                if sim.H < 1.01*model.H_ref:
                    sim.flush_freq = 2
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_2(lat, V, sim, lat.dtau)

        elif order == 4:
            "Solve the non-linear evolution:"
            while (sim.H > 0.99*model.H_ref):
                if sim.H < 1.01*model.H_ref:
                    sim.flush_freq = 2
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_4(lat, V, sim, lat.dtau)

        elif order == 6:
            "Solve the non-linear evolution:"
            while (sim.H > 0.99*model.H_ref):
                if sim.H < 1.01*model.H_ref:
                    sim.flush_freq = 2
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_6(lat, V, sim, lat.dtau)

        elif order == 8:
            "Solve the non-linear evolution:"
            while (sim.H > 0.99*model.H_ref):
                if sim.H < 1.01*model.H_ref:
                    sim.flush_freq = 2
                if (sim.i0%(sim.flush_freq)==0):
                    evo.calc_rho_pres(lat, V, sim, print_Q, print_w)
                    data_file = sim.flush(lat, path)

                    "Calculate spectrums and statistics:"
                    if lat.postQ:
                        postp.process_fields(lat, V, sim, data_file)

                sim.i0 += 1
                "Change this for a higher-order integrator if needed:"
                evo.evo_step_8(lat, V, sim, lat.dtau)

